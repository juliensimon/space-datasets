"""Dataset validation with CI-friendly output."""

from __future__ import annotations

import sys

import pandas as pd


def check_dataset(
    df: pd.DataFrame,
    dataset_name: str,
    min_rows: int,
    expected_columns: list[str] | None = None,
    critical_columns: list[str] | None = None,
    max_null_pct: float = 0.05,
    warn_all_nulls: float | None = None,
    previous_rows: int | None = None,
    max_row_drop_pct: float = 0.20,
    fail_on_drop: bool = False,
) -> None:
    """Validate a DataFrame before publishing.

    Hard-fails (sys.exit(1)) on row count below minimum, missing columns,
    or entirely-null columns. Emits GitHub Actions ::warning:: annotations
    for null thresholds and row count drops.

    Args:
        df: DataFrame to validate.
        dataset_name: Name for error messages.
        min_rows: Minimum acceptable row count (hard fail).
        expected_columns: Columns that must exist (hard fail if missing).
        critical_columns: Columns where high null % triggers a warning.
        max_null_pct: Null fraction threshold for critical columns.
        warn_all_nulls: If set, check every non-critical column against this
            null fraction threshold and emit a warning for any that exceed it.
            Use to catch unexpectedly sparse columns across the whole DataFrame.
        previous_rows: Previous row count for trend checking.
        max_row_drop_pct: Maximum acceptable row count drop fraction.
        fail_on_drop: If True, hard-fail (sys.exit(1)) on row count drop
            exceeding max_row_drop_pct instead of emitting a warning.
            Use for incremental pipelines where data loss is critical.
    """
    n_rows = len(df)
    warnings = 0

    # Hard fail: row count
    if n_rows < min_rows:
        print(f"::error::{dataset_name}: only {n_rows:,} rows (minimum: {min_rows:,})")
        sys.exit(1)

    # Hard fail: missing columns
    if expected_columns:
        missing = [c for c in expected_columns if c not in df.columns]
        if missing:
            print(f"::error::{dataset_name}: missing columns: {missing}")
            sys.exit(1)

    # Hard fail: entirely-null columns (skip for empty DataFrames — vacuous truth)
    if len(df) > 0:
        all_null = [c for c in df.columns if df[c].isna().all()]
    else:
        all_null = []
    if all_null:
        print(f"::error::{dataset_name}: columns are entirely null: {all_null}")
        sys.exit(1)

    # Warning: critical column nulls
    if critical_columns:
        for col in critical_columns:
            if col in df.columns:
                null_frac = df[col].isna().mean()
                if null_frac > max_null_pct:
                    print(
                        f"::warning::{dataset_name}: {col} has "
                        f"{null_frac:.1%} nulls (threshold: {max_null_pct:.1%})"
                    )
                    warnings += 1

    # Warning: all-column null sweep (skips columns already checked as critical)
    if warn_all_nulls is not None:
        checked = set(critical_columns or [])
        for col in df.columns:
            if col not in checked:
                null_frac = df[col].isna().mean()
                if null_frac > warn_all_nulls:
                    print(f"::warning::{dataset_name}: {col} has {null_frac:.1%} nulls")
                    warnings += 1

    # Warning (or hard fail): row trend
    if previous_rows is not None and previous_rows > 0:
        drop_frac = 1.0 - (n_rows / previous_rows)
        if drop_frac > max_row_drop_pct:
            if fail_on_drop:
                print(
                    f"::error::{dataset_name}: row count dropped "
                    f"{drop_frac:.1%} ({previous_rows:,} → {n_rows:,})"
                )
                sys.exit(1)
            else:
                print(
                    f"::warning::{dataset_name}: row count dropped "
                    f"{drop_frac:.1%} ({previous_rows:,} → {n_rows:,})"
                )
                warnings += 1

    status = f"{n_rows:,} rows"
    if warnings:
        status += f", {warnings} warning(s)"
    print(f"  Validation OK: {dataset_name} — {status}")
