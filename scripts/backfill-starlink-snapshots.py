#!/usr/bin/env python3
"""
Backfill missing daily_snapshots from Space-Track GP History API.

Fetches one day at a time with conservative rate limiting to avoid bans.
Saves progress after each day so it can be safely interrupted and resumed.

Usage:
    # Set credentials
    export SPACETRACK_USER=you@example.com
    export SPACETRACK_PASS=yourpassword

    # Backfill missing days (dry run — no HF upload)
    python scripts/backfill-starlink-snapshots.py

    # Backfill and upload to HF when done
    python scripts/backfill-starlink-snapshots.py --upload

    # Custom date range
    python scripts/backfill-starlink-snapshots.py --start 2026-01-15 --end 2026-02-15

    # Adjust delay between requests (default: 30s)
    python scripts/backfill-starlink-snapshots.py --delay 45
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

# ── Reuse classification logic from update-starlink.py ───────────────────────

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

SPACETRACK_LOGIN = "https://www.space-track.org/ajaxauth/login"
SPACETRACK_GP_HISTORY = (
    "https://www.space-track.org/basicspacedata/query"
    "/class/gp_history"
    "/OBJECT_NAME/STARLINK~~"
    "/EPOCH/{start}--{end}"
    "/orderby/NORAD_CAT_ID,EPOCH"
    "/format/json"
)

PROGRESS_FILE = Path(__file__).parent.parent / "data" / "backfill-progress.json"
HF_REPO = "juliensimon/starlink-fleet-data"


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


# ── Space-Track session ──────────────────────────────────────────────────────

def login(session: requests.Session) -> None:
    user = os.environ.get("SPACETRACK_USER")
    pw = os.environ.get("SPACETRACK_PASS")
    if not user or not pw:
        print("Set SPACETRACK_USER and SPACETRACK_PASS environment variables.")
        sys.exit(1)
    resp = session.post(SPACETRACK_LOGIN, data={"identity": user, "password": pw})
    resp.raise_for_status()
    print("Logged in to Space-Track.")


def fetch_day(session: requests.Session, day: datetime) -> list[dict]:
    """Fetch all Starlink GP records for a single day."""
    start = day.strftime("%Y-%m-%d")
    end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    url = SPACETRACK_GP_HISTORY.format(start=start, end=end)
    resp = session.get(url, timeout=120)
    resp.raise_for_status()
    return resp.json()


# ── Aggregation (same logic as update-starlink.py) ───────────────────────────

def aggregate_day(records: list[dict], day: datetime) -> pd.DataFrame | None:
    """Classify satellites and build per-shell aggregates for one day."""
    ref_time = day.replace(hour=23, minute=59, tzinfo=timezone.utc)
    rows = []

    for r in records:
        name = r.get("OBJECT_NAME", "")
        if not name.startswith("STARLINK"):
            continue

        inc = float(r["INCLINATION"])
        ecc = float(r["ECCENTRICITY"])
        mm = float(r["MEAN_MOTION"])
        mm_dot = float(r.get("MEAN_MOTION_DOT", 0))
        alt = altitude_from_mean_motion(mm, ecc)

        if alt < 0 or alt > 2000:
            continue

        epoch_str = r["EPOCH"]
        if epoch_str.endswith("Z"):
            epoch_str = epoch_str[:-1] + "+00:00"
        epoch = datetime.fromisoformat(epoch_str)
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)
        epoch_age_hours = (ref_time - epoch).total_seconds() / 3600

        intl = r.get("OBJECT_ID", "")
        launch_year = int(intl[:4]) if intl and intl[:4].isdigit() else 0

        shell_id = get_shell_id(inc)
        status = classify_status(alt, inc, ecc, epoch_age_hours, mm_dot)

        rows.append({
            "norad_id": int(r["NORAD_CAT_ID"]),
            "shell_id": shell_id,
            "status": status,
            "is_isl_capable": is_isl_capable(inc, launch_year),
        })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    # Keep latest epoch per satellite (same dedup as daily pipeline)
    df = df.drop_duplicates("norad_id", keep="last")

    today = pd.Timestamp(day.strftime("%Y-%m-%d"))
    daily_rows = []
    for sid in sorted(df["shell_id"].unique()):
        shell = df[df["shell_id"] == sid]
        daily_rows.append({
            "date": today,
            "shell_id": int(sid),
            "shell_name": SHELL_NAMES.get(int(sid), "Unknown"),
            "total_count": len(shell),
            "operational_count": int((shell["status"] == "operational").sum()),
            "raising_count": int((shell["status"] == "raising").sum()),
            "deorbiting_count": int((shell["status"] == "deorbiting").sum()),
            "isl_operational_count": int(shell["is_isl_capable"].sum()),
            "new_launches": 0,
        })

    return pd.DataFrame(daily_rows)


# ── Progress tracking ────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"completed_days": [], "snapshots": []}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2, default=str) + "\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Backfill Starlink daily snapshots from Space-Track")
    parser.add_argument("--start", default="2026-01-01", help="Start date (inclusive)")
    parser.add_argument("--end", default="2026-03-20", help="End date (inclusive)")
    parser.add_argument("--delay", type=int, default=30, help="Seconds between API requests (default: 30)")
    parser.add_argument("--upload", action="store_true", help="Upload to HF when done")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")
    delay = args.delay

    # Build list of days to fetch
    all_days = []
    d = start
    while d <= end:
        all_days.append(d)
        d += timedelta(days=1)

    # Load progress
    progress = load_progress()
    completed = set(progress["completed_days"])
    remaining = [d for d in all_days if d.strftime("%Y-%m-%d") not in completed]

    print(f"Date range: {args.start} to {args.end} ({len(all_days)} days)")
    print(f"Already completed: {len(completed)}")
    print(f"Remaining: {len(remaining)}")
    print(f"Delay between requests: {delay}s")
    print()

    if not remaining:
        print("Nothing to backfill!")
    else:
        session = requests.Session()
        login(session)
        print()

        for i, day in enumerate(remaining):
            day_str = day.strftime("%Y-%m-%d")
            print(f"[{i+1}/{len(remaining)}] Fetching {day_str}...", end=" ", flush=True)

            try:
                records = fetch_day(session, day)
                print(f"{len(records):,} records.", end=" ", flush=True)

                df_day = aggregate_day(records, day)
                if df_day is not None:
                    progress["snapshots"].extend(df_day.to_dict("records"))
                    total_sats = df_day["total_count"].sum()
                    operational = df_day["operational_count"].sum()
                    print(f"{total_sats:,} sats ({operational:,} operational).")
                else:
                    print("No Starlink data.")

                progress["completed_days"].append(day_str)
                save_progress(progress)

            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    print(f"\nRate limited! Waiting 5 minutes...")
                    time.sleep(300)
                    # Don't mark as completed — will retry next run
                    continue
                else:
                    print(f"\nHTTP error: {e}")
                    print("Saving progress and exiting. Re-run to resume.")
                    save_progress(progress)
                    sys.exit(1)
            except Exception as e:
                print(f"\nError: {e}")
                print("Saving progress and exiting. Re-run to resume.")
                save_progress(progress)
                sys.exit(1)

            # Be gentle
            if i < len(remaining) - 1:
                print(f"  Waiting {delay}s...", flush=True)
                time.sleep(delay)

    # Merge with existing daily_snapshots
    if not progress["snapshots"]:
        print("No snapshots to merge.")
        return

    df_backfill = pd.DataFrame(progress["snapshots"])
    df_backfill["date"] = pd.to_datetime(df_backfill["date"])
    print(f"\nBackfill data: {len(df_backfill)} rows, "
          f"{df_backfill['date'].dt.date.nunique()} days")

    if not args.upload:
        print("\nDry run — skipping HF upload. Use --upload to merge and push.")
        print(f"Progress saved to {PROGRESS_FILE}")
        return

    # Download existing, merge, upload
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        data_dir = tmp_dir / "data"
        data_dir.mkdir()
        daily_path = data_dir / "daily_snapshots.parquet"

        print("Downloading existing daily_snapshots...")
        subprocess.run(
            ["hf", "download", HF_REPO, "data/daily_snapshots.parquet",
             "--repo-type", "dataset", "--local-dir", str(tmp_dir)],
            check=True, capture_output=True, timeout=60,
        )

        df_existing = pd.read_parquet(daily_path)
        df_existing["date"] = pd.to_datetime(df_existing["date"])

        # Remove any existing rows for backfilled dates (idempotent)
        backfill_dates = set(df_backfill["date"].dt.date.unique())
        df_existing = df_existing[~df_existing["date"].dt.date.isin(backfill_dates)]

        df_merged = pd.concat([df_existing, df_backfill], ignore_index=True)
        df_merged = df_merged.sort_values(["date", "shell_id"]).reset_index(drop=True)

        print(f"Merged: {len(df_existing)} existing + {len(df_backfill)} backfill = "
              f"{len(df_merged)} total rows, "
              f"{df_merged['date'].dt.date.nunique()} days")

        df_merged.to_parquet(daily_path, index=False, engine="pyarrow", compression="zstd")

        print("Uploading to HF...")
        subprocess.run(
            ["hf", "upload", HF_REPO, str(daily_path), "data/daily_snapshots.parquet",
             "--repo-type", "dataset",
             "--commit-message", f"Backfill daily_snapshots: {len(backfill_dates)} days ({min(backfill_dates)} to {max(backfill_dates)})"],
            check=True,
        )

    # Clean up progress file
    PROGRESS_FILE.unlink(missing_ok=True)
    print("Done! Progress file cleaned up.")


if __name__ == "__main__":
    main()
