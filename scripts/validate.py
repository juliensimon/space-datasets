#!/usr/bin/env python3
"""Shared data quality checks for dataset pipelines."""

import json
import sys
from pathlib import Path

import pandas as pd

STATUS_FILE = Path(__file__).parent.parent / "status.json"


def check_dataset(
    df: pd.DataFrame,
    dataset_name: str,
    min_rows: int,
    expected_columns: list[str],
    critical_columns: list[str] | None = None,
    max_null_pct: float = 0.05,
) -> None:
    """Validate a DataFrame before upload.

    Hard fails (SystemExit) on row count below minimum or missing columns.
    Prints ::warning:: annotations for null percentage violations.
    """
    warnings = 0

    # ── Row count ────────────────────────────────────────────────────────
    if len(df) < min_rows:
        print(f"::error::VALIDATION FAILED [{dataset_name}]: "
              f"{len(df):,} rows < minimum {min_rows:,}")
        sys.exit(1)

    # ── Schema ───────────────────────────────────────────────────────────
    missing = set(expected_columns) - set(df.columns)
    if missing:
        print(f"::error::VALIDATION FAILED [{dataset_name}]: "
              f"missing columns: {sorted(missing)}")
        sys.exit(1)

    # ── Null checks ──────────────────────────────────────────────────────
    if critical_columns:
        for col in critical_columns:
            if col not in df.columns:
                continue
            null_pct = df[col].isna().mean()
            if null_pct > max_null_pct:
                print(f"::warning::[{dataset_name}] column '{col}' "
                      f"has {null_pct:.1%} nulls (threshold: {max_null_pct:.0%})")
                warnings += 1

    # ── Row count trend ──────────────────────────────────────────────────
    warnings += _check_row_trend(dataset_name, len(df))

    status = "0 warnings" if warnings == 0 else f"{warnings} warning(s)"
    print(f"Validation passed [{dataset_name}]: "
          f"{len(df):,} rows, {len(df.columns)} columns, {status}")


def _check_row_trend(dataset_name: str, current_rows: int, drop_warn_pct: float = 0.20) -> int:
    """Warn if row count dropped significantly from last run. Returns warning count."""
    if not STATUS_FILE.exists():
        return 0
    try:
        status = json.loads(STATUS_FILE.read_text())
        prev_rows = status.get("_rows", {}).get(dataset_name)
        if prev_rows is None:
            return 0
        if prev_rows > 0 and current_rows < prev_rows * (1 - drop_warn_pct):
            drop_pct = (prev_rows - current_rows) / prev_rows
            print(f"::warning::[{dataset_name}] row count dropped {drop_pct:.0%}: "
                  f"{prev_rows:,} -> {current_rows:,}")
            return 1
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return 0
