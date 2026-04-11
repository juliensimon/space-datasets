"""Incremental dataset update helpers."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd


def download_existing(
    repo: str,
    filename: str,
    local_dir: str | Path,
) -> pd.DataFrame | None:
    """Download an existing parquet file from a HF dataset repo.

    Returns DataFrame from the downloaded parquet, or None on any failure.
    """
    local_dir = Path(local_dir)
    parquet_path = local_dir / "data" / filename
    try:
        subprocess.run(
            ["hf", "download", repo, f"data/{filename}",
             "--repo-type", "dataset", "--local-dir", str(local_dir)],
            check=True, capture_output=True, timeout=120,
        )
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            print(f"  Loaded existing: {len(df):,} rows from {repo}")
            return df
    except Exception as e:
        print(f"  Could not load existing data ({e}), will do full rebuild")
    return None


def merge_dedup(
    df_existing: pd.DataFrame,
    df_new: pd.DataFrame,
    key: str | list[str],
    sort_by: str | list[str],
) -> pd.DataFrame:
    """Merge existing and new data, deduplicating by key (new wins)."""
    df = pd.concat([df_existing, df_new], ignore_index=True)
    df = df.drop_duplicates(subset=key, keep="last")
    df = df.sort_values(sort_by).reset_index(drop=True)
    return df


def append_by_date(
    df_existing: pd.DataFrame,
    df_new: pd.DataFrame,
    date_col: str,
    min_existing: int = 0,
) -> pd.DataFrame:
    """Append new data by replacing overlapping dates in existing data."""
    if len(df_existing) < min_existing:
        print(f"::error::Existing data has only {len(df_existing)} rows "
              f"(minimum: {min_existing}) — aborting to protect historical data")
        sys.exit(1)
    new_dates = set(df_new[date_col].unique())
    df_kept = df_existing[~df_existing[date_col].isin(new_dates)]
    df = pd.concat([df_kept, df_new], ignore_index=True)
    df = df.sort_values(date_col).reset_index(drop=True)
    return df
