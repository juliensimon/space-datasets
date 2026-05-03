"""Parquet writing and Hugging Face upload."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi


def write_parquet(
    df: pd.DataFrame,
    path: str | Path,
    compression: str = "zstd",
) -> Path:
    """Write a DataFrame to Parquet with sensible defaults."""
    path = Path(path)
    df.to_parquet(path, index=False, engine="pyarrow", compression=compression)
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Wrote {path.name}: {len(df):,} rows, {size_mb:.1f} MB")
    return path


def upload_to_hf(
    repo: str,
    local_dir: str | Path,
    commit_message: str = "Update dataset",
) -> None:
    """Upload a directory to a Hugging Face dataset repository via Python API."""
    token = os.environ.get("HF_TOKEN")
    api = HfApi(token=token)
    api.create_repo(repo, repo_type="dataset", exist_ok=True)
    api.upload_folder(
        repo_id=repo,
        folder_path=str(local_dir),
        repo_type="dataset",
        commit_message=commit_message,
    )
