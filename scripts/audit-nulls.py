#!/usr/bin/env python3
"""Audit all HF datasets under juliensimon/ for columns with high null percentages.

Uses PyArrow to compute null counts efficiently (row-group-at-a-time),
so even multi-million-row datasets stay under a few MB of memory.

Usage:
    python scripts/audit-nulls.py                    # audit all datasets, 80% threshold
    python scripts/audit-nulls.py --threshold 0.90   # only flag >90% null
    python scripts/audit-nulls.py --dataset neo       # audit a single dataset
    python scripts/audit-nulls.py --json-only         # suppress console table
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import HfApi, hf_hub_download

AUTHOR = "juliensimon"
EXCLUDE = {
    "amazon-shoe-reviews",
    "autonlp-data-song-lyrics",
    "autonlp-data-imdb-demo-hf",
    "food102",
}
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "audit"


def find_parquet_files(api: HfApi, repo_id: str) -> list[str]:
    """Return paths of all .parquet files under data/ in a dataset repo."""
    try:
        files = api.list_repo_tree(
            repo_id, path_in_repo="data", repo_type="dataset"
        )
        return [f.rfilename for f in files if f.rfilename.endswith(".parquet")]
    except Exception:
        return []


def compute_null_stats(parquet_path: str) -> list[dict]:
    """Compute null percentage per column using PyArrow row-group iteration."""
    pf = pq.ParquetFile(parquet_path)
    num_rows = pf.metadata.num_rows
    if num_rows == 0:
        return []

    schema = pf.schema_arrow
    results = []
    for i in range(len(schema)):
        col_name = schema.field(i).name
        col_type = str(schema.field(i).type)
        null_count = 0
        for rg in range(pf.metadata.num_row_groups):
            col_data = pf.read_row_group(rg, columns=[col_name]).column(0)
            null_count += col_data.null_count
        null_pct = null_count / num_rows
        results.append({
            "column": col_name,
            "dtype": col_type,
            "null_pct": round(null_pct, 4),
            "null_count": null_count,
            "total_rows": num_rows,
        })
    return results


def audit_dataset(
    api: HfApi, repo_id: str, threshold: float
) -> dict | None:
    """Audit a single dataset repo. Returns result dict or None on error."""
    short_name = repo_id.replace(f"{AUTHOR}/", "")
    parquet_files = find_parquet_files(api, repo_id)
    if not parquet_files:
        print(f"  {short_name}: no parquet files found, skipping")
        return None

    all_flagged = []
    total_rows = 0
    total_cols = 0

    for pq_path in parquet_files:
        try:
            local_path = hf_hub_download(
                repo_id, pq_path, repo_type="dataset"
            )
        except Exception as e:
            print(f"  {short_name}/{pq_path}: download failed ({e})")
            continue

        stats = compute_null_stats(local_path)
        if not stats:
            continue

        total_rows = stats[0]["total_rows"]
        total_cols += len(stats)

        flagged = [s for s in stats if s["null_pct"] >= threshold]
        for f in flagged:
            f["file"] = pq_path
        all_flagged.extend(flagged)

    if total_cols == 0:
        return None

    return {
        "repo_id": repo_id,
        "total_rows": total_rows,
        "total_columns": total_cols,
        "flagged_columns": sorted(
            all_flagged, key=lambda x: x["null_pct"], reverse=True
        ),
    }


def severity(null_pct: float) -> str:
    if null_pct >= 0.95:
        return "critical"
    if null_pct >= 0.90:
        return "high"
    return "moderate"


def print_summary(results: dict, threshold: float) -> None:
    """Print a human-readable summary to console."""
    flagged_datasets = {
        k: v for k, v in results["datasets"].items() if v["flagged_columns"]
    }
    if not flagged_datasets:
        print("\nNo columns exceed the threshold — all clean!")
        return

    # Group flagged columns by severity
    tiers = {"critical": [], "high": [], "moderate": []}
    for ds_name, ds_info in flagged_datasets.items():
        for col in ds_info["flagged_columns"]:
            tier = severity(col["null_pct"])
            tiers[tier].append((ds_name, col))

    for tier_name, label in [
        ("critical", "Critical (>95% null)"),
        ("high", "High (90-95% null)"),
        ("moderate", f"Moderate ({threshold:.0%}-90% null)"),
    ]:
        entries = tiers[tier_name]
        if not entries:
            continue
        print(f"\n{'='*60}")
        print(f"  {label} — {len(entries)} columns across "
              f"{len(set(e[0] for e in entries))} datasets")
        print(f"{'='*60}")
        print(f"  {'Dataset':<35} {'Column':<30} {'Null%':>6}  {'Type'}")
        print(f"  {'─'*35} {'─'*30} {'─'*6}  {'─'*15}")
        for ds_name, col in sorted(entries, key=lambda x: x[1]["null_pct"], reverse=True):
            print(f"  {ds_name:<35} {col['column']:<30} "
                  f"{col['null_pct']:5.1%}  {col['dtype']}")

    total_flagged = sum(len(v["flagged_columns"]) for v in flagged_datasets.values())
    clean = results["datasets_scanned"] - len(flagged_datasets)
    print(f"\n{'─'*60}")
    print(f"  Total flagged columns: {total_flagged}")
    print(f"  Datasets with issues:  {len(flagged_datasets)}")
    print(f"  Datasets clean:        {clean}")
    print(f"{'─'*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Audit HF datasets for mostly-null columns"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.80,
        help="Null percentage threshold for flagging (default: 0.80)",
    )
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="Audit a single dataset by short name (e.g., 'exoplanets')",
    )
    parser.add_argument(
        "--json-only", action="store_true",
        help="Suppress console output, only write JSON",
    )
    args = parser.parse_args()

    api = HfApi()

    # Discover datasets
    if args.dataset:
        repo_ids = [f"{AUTHOR}/{args.dataset}"]
    else:
        all_datasets = list(api.list_datasets(author=AUTHOR))
        repo_ids = [
            d.id for d in all_datasets
            if d.id.replace(f"{AUTHOR}/", "") not in EXCLUDE
        ]
        repo_ids.sort()

    print(f"Auditing {len(repo_ids)} dataset(s), threshold={args.threshold:.0%}\n")

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold": args.threshold,
        "datasets_scanned": 0,
        "datasets_with_issues": 0,
        "datasets": {},
    }

    for idx, repo_id in enumerate(repo_ids, 1):
        short_name = repo_id.replace(f"{AUTHOR}/", "")
        try:
            ds_result = audit_dataset(api, repo_id, args.threshold)
        except Exception as e:
            print(f"[{idx}/{len(repo_ids)}] {short_name}: ERROR — {e}")
            continue

        results["datasets_scanned"] += 1
        if ds_result is None:
            print(f"[{idx}/{len(repo_ids)}] {short_name}: skipped")
            continue

        n_flagged = len(ds_result["flagged_columns"])
        results["datasets"][short_name] = ds_result
        if n_flagged > 0:
            results["datasets_with_issues"] += 1
        print(
            f"[{idx}/{len(repo_ids)}] {short_name}: "
            f"{ds_result['total_columns']} columns, {n_flagged} flagged"
        )

        # Small delay between datasets to be nice to HF API
        if not args.dataset and idx < len(repo_ids):
            time.sleep(0.3)

    # Write JSON report
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "null-audit.json"
    json_path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nJSON report written to {json_path}")

    # Print console summary
    if not args.json_only:
        print_summary(results, args.threshold)


if __name__ == "__main__":
    main()
