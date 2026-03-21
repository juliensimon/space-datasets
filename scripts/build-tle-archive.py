#!/usr/bin/env python3
"""
Build the Space-Track TLE Archive dataset from yearly bulk zip files.

Streams raw 2-line TLE data from Space-Track bulk exports, parses all objects,
and writes one Parquet file per year. No filtering — includes every tracked object.

Download zips from: https://ln5.sync.com/dl/afd354190/c5cd2q72-a5qjzp4q-nbjdiqkr-cenajuqu

Usage: python scripts/build-tle-archive.py [--dir ~/Downloads] [--out data/tle-archive] [--upload]
"""

import argparse
import math
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from io import TextIOWrapper
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# WGS-84 constants
MU = 398600.4418  # km³/s²
R_EARTH = 6371.0  # km


def altitude_from_mean_motion(n_rev_per_day: float, ecc: float) -> float:
    """Compute perigee altitude from mean motion (rev/day) and eccentricity."""
    if n_rev_per_day <= 0:
        return -1.0
    n_rad_s = n_rev_per_day * 2 * math.pi / 86400.0
    a = (MU / (n_rad_s**2)) ** (1.0 / 3.0)
    return a * (1 - ecc) - R_EARTH


def parse_scientific(s: str) -> float:
    """Parse Space-Track pseudo-scientific notation: ' 12345-6' -> 0.12345e-6."""
    s = s.strip()
    if not s or s in ("00000-0", "00000+0"):
        return 0.0
    m = re.match(r"^([+-]?)(\d+)([+-]\d+)$", s)
    if not m:
        return 0.0
    sign = -1 if m.group(1) == "-" else 1
    mantissa = float("0." + m.group(2))
    exponent = int(m.group(3))
    return sign * mantissa * (10**exponent)


def epoch_to_datetime(year: int, day: float) -> datetime:
    """Convert TLE epoch (year + fractional day) to datetime."""
    base = datetime(year, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(days=day - 1)


def parse_tle_pair(line1: str, line2: str) -> dict | None:
    """Parse a TLE line pair into a record dict."""
    try:
        norad_id = int(line1[2:7].strip())
        intl_des = line1[9:17].strip()

        epoch_yr = int(line1[18:20].strip())
        epoch_year = 1900 + epoch_yr if epoch_yr >= 57 else 2000 + epoch_yr
        epoch_day = float(line1[20:32].strip())
        epoch_dt = epoch_to_datetime(epoch_year, epoch_day)

        ndot = float(line1[33:43].strip())
        bstar = parse_scientific(line1[53:61].strip())

        inclination = float(line2[8:16].strip())
        raan = float(line2[17:25].strip())
        ecc = float("0." + line2[26:33].strip())
        arg_perigee = float(line2[34:42].strip())
        mean_anomaly = float(line2[43:51].strip())
        mean_motion = float(line2[52:63].strip())

        altitude = altitude_from_mean_motion(mean_motion, ecc)

        return {
            "norad_id": norad_id,
            "epoch": epoch_dt,
            "inclination": round(inclination, 4),
            "raan": round(raan, 4),
            "eccentricity": ecc,
            "arg_perigee": round(arg_perigee, 4),
            "mean_anomaly": round(mean_anomaly, 4),
            "mean_motion": round(mean_motion, 8),
            "mean_motion_dot": ndot,
            "bstar": bstar,
            "intl_designator": intl_des,
            "altitude_km": round(altitude, 2),
        }
    except (ValueError, IndexError):
        return None


SCHEMA = pa.schema(
    [
        ("norad_id", pa.int32()),
        ("epoch", pa.timestamp("us", tz="UTC")),
        ("inclination", pa.float32()),
        ("raan", pa.float32()),
        ("eccentricity", pa.float32()),
        ("arg_perigee", pa.float32()),
        ("mean_anomaly", pa.float32()),
        ("mean_motion", pa.float64()),
        ("mean_motion_dot", pa.float64()),
        ("bstar", pa.float64()),
        ("intl_designator", pa.string()),
        ("altitude_km", pa.float32()),
    ]
)


def find_txt_in_zip(zip_path: str) -> str:
    """Find the TLE txt filename inside a zip, ignoring __MACOSX."""
    result = subprocess.run(
        ["unzip", "-l", zip_path], capture_output=True, text=True
    )
    for line in result.stdout.split("\n"):
        if "__MACOSX" in line:
            continue
        m = re.search(r"(\S*tle\S*\.txt)\s*$", line)
        if m:
            return m.group(1)
    # Fallback
    return Path(zip_path).stem.replace(".txt", "") + ".txt"


def process_zip(
    zip_path: str, out_dir: Path, writers: dict, batch_size: int = 500_000
) -> dict:
    """Stream a TLE zip file and write to parquet. Writers are shared across zips."""
    txt_name = find_txt_in_zip(zip_path)
    print(f"  Streaming {txt_name}...")

    proc = subprocess.Popen(
        ["unzip", "-p", zip_path, txt_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    records = []
    prev_line = None
    total = 0
    written = 0
    line_count = 0

    for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").rstrip()
        line_count += 1

        if prev_line is None:
            if line.startswith("1 "):
                prev_line = line
            continue

        if not line.startswith("2 "):
            prev_line = line if line.startswith("1 ") else None
            continue

        line1 = prev_line
        line2 = line
        prev_line = None

        record = parse_tle_pair(line1, line2)
        if record is None:
            continue

        total += 1
        records.append(record)

        if len(records) >= batch_size:
            written += flush_records(records, out_dir, writers)
            print(
                f"    {total:,} TLEs parsed, {written:,} written ({line_count:,} lines)..."
            )
            records = []

    if records:
        written += flush_records(records, out_dir, writers)

    proc.wait()

    return {"total": total, "written": written, "lines": line_count}


def flush_records(records: list[dict], out_dir: Path, writers: dict) -> int:
    """Write records to per-year parquet files using batched appending."""
    # Group by year
    by_year: dict[int, list[dict]] = {}
    for r in records:
        year = r["epoch"].year
        by_year.setdefault(year, []).append(r)

    written = 0
    for year, year_records in by_year.items():
        table = pa.Table.from_pylist(year_records, schema=SCHEMA)

        if year not in writers:
            path = out_dir / f"tle_{year}.parquet"
            writers[year] = (
                pq.ParquetWriter(str(path), SCHEMA, compression="zstd"),
                path,
            )

        writers[year][0].write_table(table)
        written += len(year_records)

    return written


def main():
    parser = argparse.ArgumentParser(description="Build Space-Track TLE Archive")
    parser.add_argument("--dir", default=str(Path.home() / "Downloads"))
    parser.add_argument(
        "--out",
        default=str(
            Path(__file__).parent.parent / "data" / "tle-archive"
        ),
    )
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    src_dir = Path(args.dir)
    out_dir = Path(args.out)

    # Find all TLE zips
    zips = sorted(src_dir.glob("tle*.txt.zip"))
    if not zips:
        print(f"No TLE zip files found in {src_dir}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Space-Track TLE Archive Builder ===")
    print(f"  Source: {src_dir}")
    print(f"  Output: {out_dir}")
    print(f"  Files:  {len(zips)}")
    total_size = sum(z.stat().st_size for z in zips) / 1024 / 1024 / 1024
    print(f"  Total:  {total_size:.1f} GB compressed")

    grand_total = 0
    grand_written = 0
    writers = {}  # Shared across all zips so per-year files accumulate

    for i, zip_path in enumerate(zips):
        size_mb = zip_path.stat().st_size / 1024 / 1024
        print(f"\n[{i + 1}/{len(zips)}] {zip_path.name} ({size_mb:.0f} MB)")

        stats = process_zip(str(zip_path), out_dir, writers)
        grand_total += stats["total"]
        grand_written += stats["written"]
        print(
            f"  TLEs: {stats['total']:,} parsed, {stats['written']:,} written"
        )

    # Close all writers
    for year, (writer, path) in writers.items():
        writer.close()
    print(f"\nClosed {len(writers)} parquet writers")

    # Summary
    parquets = sorted(out_dir.glob("tle_*.parquet"))
    total_size_mb = sum(p.stat().st_size for p in parquets) / 1024 / 1024

    print("\n=== Summary ===")
    print(f"  Total TLEs parsed:  {grand_total:,}")
    print(f"  Total written:      {grand_written:,}")
    print(f"  Parquet files:      {len(parquets)}")
    print(f"  Total size:         {total_size_mb:.1f} MB")
    for p in parquets:
        size = p.stat().st_size / 1024 / 1024
        print(f"    {p.name}: {size:.1f} MB")

    # Upload
    if args.upload:
        print("\nUploading to HF...")
        subprocess.run(
            [
                "hf",
                "upload",
                "juliensimon/space-track-tle-history",
                str(out_dir),
                "data",
                "--repo-type",
                "dataset",
            ],
            check=True,
        )
        print("Done.")


if __name__ == "__main__":
    main()
