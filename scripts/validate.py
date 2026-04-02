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
    incremental: bool = False,
    warn_all_nulls: float | None = None,
) -> None:
    """Validate a DataFrame before upload.

    Hard fails (SystemExit) on row count below minimum or missing columns.
    For incremental datasets, also hard-fails on >20% row count drop
    (protects against uploading truncated data over good data).
    Prints ::warning:: annotations for null percentage violations.

    If warn_all_nulls is set, checks ALL columns (not just critical_columns)
    against that threshold and warns on any that exceed it.
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

    # ── Null checks (critical columns) ───────────────────────────────────
    if critical_columns:
        for col in critical_columns:
            if col not in df.columns:
                continue
            null_pct = df[col].isna().mean()
            if null_pct > max_null_pct:
                print(f"::warning::[{dataset_name}] column '{col}' "
                      f"has {null_pct:.1%} nulls (threshold: {max_null_pct:.0%})")
                warnings += 1

    # ── Null checks (all columns) ────────────────────────────────────────
    if warn_all_nulls is not None:
        checked = set(critical_columns or [])
        for col in df.columns:
            if col in checked:
                continue
            null_pct = df[col].isna().mean()
            if null_pct > warn_all_nulls:
                print(f"::warning::[{dataset_name}] column '{col}' "
                      f"has {null_pct:.1%} nulls (>{warn_all_nulls:.0%})")
                warnings += 1

    # ── Row count trend ──────────────────────────────────────────────────
    warnings += _check_row_trend(dataset_name, len(df), fail_on_drop=incremental)

    status = "0 warnings" if warnings == 0 else f"{warnings} warning(s)"
    print(f"Validation passed [{dataset_name}]: "
          f"{len(df):,} rows, {len(df.columns)} columns, {status}")


def _check_row_trend(
    dataset_name: str,
    current_rows: int,
    drop_warn_pct: float = 0.20,
    fail_on_drop: bool = False,
) -> int:
    """Check row count against previous run.

    For incremental datasets (fail_on_drop=True), a >20% drop is a hard failure
    — this prevents uploading truncated data over good data on HF.
    For full-rebuild datasets, the same drop is a warning only.
    """
    if not STATUS_FILE.exists():
        return 0
    try:
        status = json.loads(STATUS_FILE.read_text())
        prev_rows = status.get("_rows", {}).get(dataset_name)
        if prev_rows is None:
            return 0
        if prev_rows > 0 and current_rows < prev_rows * (1 - drop_warn_pct):
            drop_pct = (prev_rows - current_rows) / prev_rows
            if fail_on_drop:
                print(f"::error::VALIDATION FAILED [{dataset_name}]: "
                      f"row count dropped {drop_pct:.0%} ({prev_rows:,} -> {current_rows:,}). "
                      f"Aborting to protect existing HF data. "
                      f"If this is expected, update status.json manually.")
                sys.exit(1)
            else:
                print(f"::warning::[{dataset_name}] row count dropped {drop_pct:.0%}: "
                      f"{prev_rows:,} -> {current_rows:,}")
                return 1
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return 0
